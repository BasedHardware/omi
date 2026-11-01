import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ChatPauseCard } from '../ChatBudgetPause';
import type { ChatAtCap } from '@/lib/omiApi.generated';

describe('chat budget pause', () => {
  it('renders backend reset copy and invokes the upgrade path', () => {
    const onUpgrade = vi.fn();
    const state: ChatAtCap = {
      state: 'paused',
      title: 'Chat is paused',
      body: 'Capture continues.',
      reset_at: 1793491200,
      reset_line: 'Chat is back on Nov 1.',
      trigger: 'usage_budget',
      upgrade_plan: 'architect',
      upgrade_label: 'Upgrade to Architect',
    };
    render(<ChatPauseCard state={state} onUpgrade={onUpgrade} />);
    expect(screen.getByText(state.reset_line)).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: state.upgrade_label! }));
    expect(onUpgrade).toHaveBeenCalledOnce();
  });
});
