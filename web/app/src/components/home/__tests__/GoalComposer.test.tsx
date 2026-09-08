import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { GoalComposer } from '@/components/home/GoalComposer';

function setup(onCreate = vi.fn().mockResolvedValue({ id: 'goal-1' })) {
  const onOpenChange = vi.fn();
  render(<GoalComposer open onOpenChange={onOpenChange} onCreate={onCreate} />);
  return { onCreate, onOpenChange, user: userEvent.setup() };
}

describe('GoalComposer', () => {
  it('sends the wire shape the goals API expects', async () => {
    const { onCreate, user } = setup();

    await user.type(screen.getByLabelText('Goal'), 'Read 12 books');
    await user.type(screen.getByLabelText('Target'), '12');
    await user.type(screen.getByLabelText('Unit'), 'books');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    // Matches the desktop create body exactly: title, target, unit only when
    // given. No goal_type/min/max — those are web inventions the desktop
    // clients never send.
    expect(onCreate).toHaveBeenCalledWith({
      title: 'Read 12 books',
      target_value: 12,
      unit: 'books',
    });
  });

  it('defaults a blank target to 1, as desktop does', async () => {
    const { onCreate, user } = setup();

    await user.type(screen.getByLabelText('Goal'), 'Ship the launch');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(onCreate).toHaveBeenCalledWith({
      title: 'Ship the launch',
      target_value: 1,
    });
  });

  it('omits unit entirely when the field is left blank', async () => {
    const { onCreate, user } = setup();

    await user.type(screen.getByLabelText('Goal'), 'Run 100 miles');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(onCreate).toHaveBeenCalledWith({
      title: 'Run 100 miles',
      target_value: 1,
    });
  });

  it('trims the title rather than sending the backend blank-title input', async () => {
    const { onCreate, user } = setup();

    await user.type(screen.getByLabelText('Goal'), '  Meditate daily  ');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(onCreate).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Meditate daily' }),
    );
  });

  it('refuses to submit an empty title', async () => {
    const { onCreate, user } = setup();

    expect(screen.getByRole('button', { name: 'Set goal' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Set goal' }));
    expect(onCreate).not.toHaveBeenCalled();
  });

  it('coerces a zero or invalid target to 1 rather than letting the API 422', async () => {
    const { onCreate, user } = setup();

    await user.type(screen.getByLabelText('Goal'), 'Read books');
    await user.type(screen.getByLabelText('Target'), '0');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(onCreate).toHaveBeenCalledWith({
      title: 'Read books',
      target_value: 1,
    });
  });

  it('closes on success', async () => {
    const { onOpenChange, user } = setup();

    await user.type(screen.getByLabelText('Goal'), 'Read books');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('stays open and explains itself when the create fails', async () => {
    const { onOpenChange, user } = setup(vi.fn().mockResolvedValue(null));

    await user.type(screen.getByLabelText('Goal'), 'Read books');
    await user.click(screen.getByRole('button', { name: 'Set goal' }));

    expect(
      await screen.findByText('Could not save that goal. Try again.'),
    ).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
