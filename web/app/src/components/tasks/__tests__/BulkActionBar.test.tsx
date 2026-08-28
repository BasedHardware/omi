import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { BulkActionBar } from '@/components/tasks/BulkActionBar';

function renderBar(onCopy = vi.fn()) {
  render(
    <BulkActionBar
      inline
      selectedCount={1}
      onComplete={vi.fn()}
      onDelete={vi.fn()}
      onSnooze={vi.fn()}
      onClear={vi.fn()}
      onCopy={onCopy}
      onExport={vi.fn()}
      onSelectAll={vi.fn()}
      onDone={vi.fn()}
    />,
  );
  return { onCopy, user: userEvent.setup() };
}

describe('BulkActionBar', () => {
  it('parks Copy and Export behind the more menu below 1600px', async () => {
    const { onCopy, user } = renderBar();

    const more = screen.getByRole('button', { name: 'More actions' });
    expect(more.className).toMatch(/min-\[1600px\]:hidden/);
    expect(screen.getByRole('button', { name: 'Copy' }).className).toMatch(
      /min-\[1600px\]:flex/,
    );

    expect(screen.getByRole('button', { name: 'Complete' }).className).toMatch(
      /min-\[1430px\]:flex/,
    );
    expect(screen.getByRole('button', { name: 'Snooze' }).parentElement).toHaveClass(
      'min-[1200px]:block',
    );

    await user.click(more);
    const menu = screen.getByRole('menu');
    expect(within(menu).getByText('Export')).toBeInTheDocument();
    expect(menu.className).toMatch(/bg-bg-secondary/);
    expect(menu.className).toMatch(/rounded-lg/);
    expect(screen.getByRole('menuitem', { name: 'Copy' }).className).toMatch(
      /cursor-pointer/,
    );
    await user.click(screen.getByRole('menuitem', { name: 'Copy' }));
    expect(onCopy).toHaveBeenCalledTimes(1);
  });

  it('closes the more menu on outside click', async () => {
    const { user } = renderBar();

    await user.click(screen.getByRole('button', { name: 'More actions' }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Select All' }));
    await waitFor(() => {
      expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    });
  });
});
