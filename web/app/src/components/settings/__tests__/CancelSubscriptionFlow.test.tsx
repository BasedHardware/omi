import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const cancelSubscription = vi.fn();
const getRetentionOffer = vi.fn();
const acceptRetentionOffer = vi.fn();

vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    capture: vi.fn(),
    identify: vi.fn(),
    reset: vi.fn(),
    setPersonProperties: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  cancelSubscription: (...args: unknown[]) => cancelSubscription(...args),
  getRetentionOffer: (...args: unknown[]) => getRetentionOffer(...args),
  acceptRetentionOffer: (...args: unknown[]) => acceptRetentionOffer(...args),
}));

import posthog from 'posthog-js';
import { CancelSubscriptionFlow } from '@/components/settings/CancelSubscriptionFlow';

const periodEnd = Math.floor(Date.UTC(2026, 11, 3, 12) / 1000);
const dateLabel = new Date(periodEnd * 1000).toLocaleDateString('en-US', {
  month: 'long',
  day: 'numeric',
  year: 'numeric',
});

const offer = {
  eligible: true,
  percent_off: 50,
  duration_months: 3,
  regular_amount: 1999,
  discounted_amount: 999,
  currency: 'usd',
};

function renderFlow() {
  const onOpenChange = vi.fn();
  const onSubscriptionUpdate = vi.fn();
  render(
    <CancelSubscriptionFlow
      open
      onOpenChange={onOpenChange}
      currentPeriodEnd={periodEnd}
      onSubscriptionUpdate={onSubscriptionUpdate}
    />,
  );
  return { onOpenChange, onSubscriptionUpdate };
}

async function reachConfirmStep() {
  fireEvent.click(screen.getByRole('button', { name: 'Too expensive' }));
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  fireEvent.change(screen.getByRole('textbox'), {
    target: { value: 'It costs too much' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  await screen.findByText('Just a moment, please');
}

describe('CancelSubscriptionFlow', () => {
  beforeEach(() => {
    cancelSubscription.mockReset();
    getRetentionOffer.mockReset();
    acceptRetentionOffer.mockReset();
    (posthog.capture as ReturnType<typeof vi.fn>).mockClear();
    getRetentionOffer.mockResolvedValue(offer);
    cancelSubscription.mockResolvedValue({
      status: 'ok',
      message: 'Subscription scheduled for cancellation.',
    });
  });

  it('asks a reason, then feedback, then shows the offer and confirms', async () => {
    const { onSubscriptionUpdate } = renderFlow();

    expect(screen.getByText('Why are you canceling?')).toBeTruthy();
    expect(screen.getByText("Can you tell us why you're leaving?")).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: 'Too expensive' }));
    expect(screen.getByRole('button', { name: 'Continue' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(screen.getByText('What price would work for you?')).toBeTruthy();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'It costs too much' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Continue' }));

    expect(await screen.findByText('Just a moment, please')).toBeTruthy();
    expect(
      await screen.findByText(/Stay and pay US\$9\.99 a month for the next 3 months\./),
    ).toBeTruthy();
    expect(
      screen.getByText(new RegExp(`Your plan will remain active until ${dateLabel}\\.`)),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Stay for 50% off' })).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Subscription' }));

    await waitFor(() => {
      expect(cancelSubscription).toHaveBeenCalledWith({
        reason: 'too_expensive',
        reasonDetails: 'It costs too much',
      });
    });
    expect(
      await screen.findByText(
        'Your subscription is set to cancel at the end of the period.',
      ),
    ).toBeTruthy();
    expect(onSubscriptionUpdate).toHaveBeenCalled();

    const confirmed = (posthog.capture as ReturnType<typeof vi.fn>).mock.calls.find(
      ([event]) => event === 'Subscription Cancel Confirmed',
    );
    expect(confirmed?.[1]).toMatchObject({
      reason: 'too_expensive',
      has_details: true,
      platform: 'web',
    });
  });

  it("treats the endpoint's ok response as a successful cancellation", async () => {
    // The real endpoint answers `{"status": "ok", "message": ...}` on both of
    // its success branches; a regression here renders a real cancellation as
    // a failure and never reaches the done screen.
    cancelSubscription.mockResolvedValueOnce({
      status: 'ok',
      message: 'Subscription scheduled for cancellation.',
    });
    const { onSubscriptionUpdate } = renderFlow();
    await reachConfirmStep();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Subscription' }));

    expect(await screen.findByText('Subscription cancelled')).toBeTruthy();
    expect(
      screen.getByText('Your subscription is set to cancel at the end of the period.'),
    ).toBeTruthy();
    expect(onSubscriptionUpdate).toHaveBeenCalled();
    expect(screen.queryByText('Failed to cancel subscription')).toBeNull();
  });

  it('shows the endpoint message when the response is not a success', async () => {
    cancelSubscription.mockResolvedValueOnce({
      status: 'error',
      message: 'No active subscription found.',
    });
    const { onSubscriptionUpdate } = renderFlow();
    await reachConfirmStep();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Subscription' }));

    expect(await screen.findByText('No active subscription found.')).toBeTruthy();
    expect(screen.queryByText('Subscription cancelled')).toBeNull();
    expect(onSubscriptionUpdate).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Cancel Subscription' })).toBeEnabled();
  });

  it('keeps cancellation reachable after a failed cancel request', async () => {
    cancelSubscription.mockRejectedValueOnce(new Error('network down'));
    renderFlow();
    await reachConfirmStep();

    const cancelButton = screen.getByRole('button', { name: 'Cancel Subscription' });
    fireEvent.click(cancelButton);

    expect(
      await screen.findByText('Failed to cancel subscription. Please try again.'),
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Cancel Subscription' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel Subscription' }));
    await waitFor(() => expect(cancelSubscription).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Subscription cancelled')).toBeTruthy();
  });

  it('offers Keep Subscription when no offer is eligible and never blocks cancel', async () => {
    getRetentionOffer.mockResolvedValue({ ...offer, eligible: false });
    const { onOpenChange } = renderFlow();
    await reachConfirmStep();

    expect(await screen.findByRole('button', { name: 'Keep Subscription' })).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Stay for/ })).toBeNull();
    expect(screen.getByRole('button', { name: 'Cancel Subscription' })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: 'Keep Subscription' }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('applies the offer with the existing endpoint', async () => {
    acceptRetentionOffer.mockResolvedValue({ ...offer, percent_off: 50 });
    const { onSubscriptionUpdate } = renderFlow();
    await reachConfirmStep();

    fireEvent.click(await screen.findByRole('button', { name: 'Stay for 50% off' }));

    await waitFor(() => expect(acceptRetentionOffer).toHaveBeenCalled());
    expect(await screen.findByText('Done. 50% off your next 3 months.')).toBeTruthy();
    expect(cancelSubscription).not.toHaveBeenCalled();
    expect(onSubscriptionUpdate).toHaveBeenCalled();
  });

  it('abandons with the current step and reason when closed early', async () => {
    const { onOpenChange } = renderFlow();
    fireEvent.click(screen.getByRole('button', { name: 'Too expensive' }));
    fireEvent.click(screen.getByRole('button', { name: 'Close' }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    const abandoned = (posthog.capture as ReturnType<typeof vi.fn>).mock.calls.find(
      ([event]) => event === 'Subscription Cancel Abandoned',
    );
    expect(abandoned?.[1]).toMatchObject({
      step: 1,
      reason: 'too_expensive',
      platform: 'web',
    });
  });
});
