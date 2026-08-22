import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { GoalDetailSheet } from '@/components/home/GoalDetailSheet';
import type { Goal } from '@/types/goals';

vi.mock('@/lib/api', () => ({
  getGoalHistory: vi.fn(),
  getGoalAdvice: vi.fn(),
}));

const api = await import('@/lib/api');

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
  const onSave = vi.fn().mockResolvedValue(true);
  const onClose = vi.fn();
  render(<GoalDetailSheet goal={goal(overrides)} onClose={onClose} onSave={onSave} />);
  return { onSave, onClose, user: userEvent.setup() };
}

function renderSheet(
  currentGoal: Goal | null,
  onSave = vi.fn().mockResolvedValue(true),
  onClose = vi.fn(),
) {
  return {
    ...render(<GoalDetailSheet goal={currentGoal} onClose={onClose} onSave={onSave} />),
    onSave,
    onClose,
    user: userEvent.setup(),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.mocked(api.getGoalHistory).mockResolvedValue([]);
});

describe('GoalDetailSheet', () => {
  it('loads history for the open goal', async () => {
    setup();

    await waitFor(() => expect(api.getGoalHistory).toHaveBeenCalledWith('goal-1'));
  });

  it('sends only the fields that changed', async () => {
    const { onSave, user } = setup();
    const title = await screen.findByLabelText('Title');

    await user.clear(title);
    await user.type(title, 'Read more books');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    // Target and unit are untouched, so they must not appear in the patch:
    // GoalUpdate uses exclude_unset, and resending them would be a no-op write.
    expect(onSave).toHaveBeenCalledWith('goal-1', { title: 'Read more books' });
  });

  it('sends a cleared unit as null rather than an empty string', async () => {
    const { onSave, user } = setup();

    await user.clear(await screen.findByLabelText('Unit'));
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(onSave).toHaveBeenCalledWith('goal-1', { unit: null });
  });

  it('keeps the edited draft open when saving fails', async () => {
    const onSave = vi.fn().mockResolvedValue(false);
    const { onClose, user } = renderSheet(goal(), onSave);
    const title = await screen.findByLabelText('Title');

    await user.clear(title);
    await user.type(title, 'Read more books');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));

    expect(
      await screen.findByText('Could not save this goal. Please try again.'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toHaveValue('Read more books');
    expect(onClose).not.toHaveBeenCalled();
  });

  it('discards an abandoned draft before reopening the same goal', async () => {
    const originalGoal = goal();
    const { rerender, user } = renderSheet(originalGoal);
    const title = await screen.findByLabelText('Title');

    await user.clear(title);
    await user.type(title, 'Abandoned draft');
    rerender(<GoalDetailSheet goal={null} onClose={vi.fn()} onSave={vi.fn()} />);
    rerender(<GoalDetailSheet goal={originalGoal} onClose={vi.fn()} onSave={vi.fn()} />);

    expect(await screen.findByLabelText('Title')).toHaveValue('Read books');
  });

  it('cannot save when nothing has changed, which the backend 400s', async () => {
    setup();

    expect(await screen.findByRole('button', { name: 'Save changes' })).toBeDisabled();
  });

  it('refuses a blank title', async () => {
    const { user } = setup();

    await user.clear(await screen.findByLabelText('Title'));

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });

  it('refuses a zero target', async () => {
    const { user } = setup();
    const target = await screen.findByLabelText('Target');

    await user.clear(target);
    await user.type(target, '0');

    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });

  it('hides target and unit for a yes/no goal', async () => {
    setup({ goal_type: 'boolean', target_value: 1, max_value: 1, unit: null });

    expect(await screen.findByLabelText('Title')).toBeInTheDocument();
    expect(screen.queryByLabelText('Target')).not.toBeInTheDocument();
  });

  it('does not request advice until asked', async () => {
    const { user } = setup();
    vi.mocked(api.getGoalAdvice).mockResolvedValue('Read 20 minutes nightly.');

    expect(api.getGoalAdvice).not.toHaveBeenCalled();

    await user.click(await screen.findByRole('button', { name: 'Get advice' }));

    expect(await screen.findByText('Read 20 minutes nightly.')).toBeInTheDocument();
  });

  it('reports an advice failure without losing the sheet', async () => {
    const { user } = setup();
    vi.mocked(api.getGoalAdvice).mockRejectedValue(new Error('rate limited'));

    await user.click(await screen.findByRole('button', { name: 'Get advice' }));

    expect(await screen.findByText('rate limited')).toBeInTheDocument();
    expect(screen.getByLabelText('Title')).toBeInTheDocument();
  });

  it('surfaces a history failure instead of an empty chart', async () => {
    vi.mocked(api.getGoalHistory).mockRejectedValue(new Error('offline'));
    setup();

    expect(await screen.findByText('offline')).toBeInTheDocument();
  });
});
