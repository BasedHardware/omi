import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TranscriptionUsageMeter } from '../TranscriptionUsageMeter';
import type { UserSubscription } from '@/types/user';

function subscription(plan: string, limit?: number, used?: number): UserSubscription {
  return {
    plan,
    status: 'active',
    is_unlimited: plan !== 'basic',
    transcription_seconds_limit: limit,
    transcription_seconds_used: used,
  };
}

describe('legacy monthly allowance presentation', () => {
  it('shows a finite server allowance for paid Plus', () => {
    render(<TranscriptionUsageMeter subscription={subscription('plus', 90000, 45000)} />);
    expect(screen.getByText('12.5 h used of 25 h')).toBeTruthy();
    expect(screen.getByText('12.5 h left')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('50');
  });
  it('uses the server Free cap and clamps over-cap remaining', () => {
    render(
      <TranscriptionUsageMeter subscription={subscription('basic', 18000, 19800)} />,
    );
    expect(screen.getByText('5.5 h used of 5 h')).toBeTruthy();
    expect(screen.getByText('0 h left')).toBeTruthy();
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('100');
  });
  it('shows no cap only when the server declares zero', () => {
    render(
      <TranscriptionUsageMeter subscription={subscription('unlimited_v2', 0, 360000)} />,
    );
    expect(screen.getByText('100 h used · No monthly listening cap')).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
  it('does not round a positive sub-minute balance down to zero', () => {
    // 90 seconds remain; formatting must not claim the allowance is gone.
    render(<TranscriptionUsageMeter subscription={subscription('plus', 18000, 17850)} />);
    expect(screen.getByText('<0.1 h left')).toBeTruthy();
  });
  it.each([
    subscription('plus'),
    subscription('future', -1, 0),
    subscription('basic', 10, NaN),
  ])('does not invent an allowance from missing or invalid data: %j', (value) => {
    render(<TranscriptionUsageMeter subscription={value} />);
    expect(screen.getByText('Listening allowance unavailable')).toBeTruthy();
    expect(screen.queryByRole('progressbar')).toBeNull();
  });
});
