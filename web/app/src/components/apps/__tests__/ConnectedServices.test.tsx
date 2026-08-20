import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ConnectedServices } from '@/components/apps/ConnectedServices';
import type { Integration } from '@/types/user';

const api = vi.hoisted(() => ({
  disconnectIntegration: vi.fn(),
  getIntegrationOAuthUrl: vi.fn(),
  getIntegrations: vi.fn(),
}));

vi.mock('@/lib/api', () => api);

const disconnected: Integration = {
  id: 'gmail',
  name: 'Gmail',
  description: 'Email integrations',
  icon: '/integrations/gmail-logo.jpeg',
  connected: false,
};

const connected: Integration = { ...disconnected, connected: true };

const createPopup = () => ({
  location: { href: '' },
  closed: false,
  close: vi.fn(),
});

describe('ConnectedServices', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.getIntegrations.mockResolvedValue([disconnected]);
    api.getIntegrationOAuthUrl.mockResolvedValue('https://example.com/oauth');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('preserves the current services and surfaces a polling refresh failure', async () => {
    const popup = createPopup();
    vi.stubGlobal(
      'open',
      vi.fn(() => popup),
    );
    api.getIntegrations
      .mockResolvedValueOnce([disconnected])
      .mockRejectedValueOnce(new Error('offline'));

    render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();

    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button'));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(screen.getByText('Gmail')).toBeVisible();
    expect(
      screen.getByText('Could not refresh external services. Please try again.'),
    ).toBeVisible();
  });

  it('opens a popup synchronously and navigates it after the OAuth URL resolves', async () => {
    let resolveOAuth!: (url: string) => void;
    const oauthUrl = new Promise<string>((resolve) => {
      resolveOAuth = resolve;
    });
    const popup = createPopup();
    const open = vi.fn(() => popup);
    vi.stubGlobal('open', open);
    api.getIntegrationOAuthUrl.mockReturnValue(oauthUrl);

    render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();

    fireEvent.click(screen.getByRole('button'));

    expect(open).toHaveBeenCalledWith('', '_blank', 'width=600,height=700');
    expect(api.getIntegrationOAuthUrl).toHaveBeenCalledWith('gmail');
    expect(popup.location.href).toBe('');

    resolveOAuth('https://example.com/oauth');
    await waitFor(() => expect(popup.location.href).toBe('https://example.com/oauth'));
  });

  it('surfaces a blocked popup without requesting an OAuth URL', async () => {
    vi.stubGlobal(
      'open',
      vi.fn(() => null),
    );

    render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();

    fireEvent.click(screen.getByRole('button'));

    expect(
      screen.getByText('Pop-up was blocked. Allow pop-ups and try again.'),
    ).toBeVisible();
    expect(api.getIntegrationOAuthUrl).not.toHaveBeenCalled();
  });

  it('does not overlap polls and stops after observing a connection', async () => {
    let resolvePoll!: (integrations: Integration[]) => void;
    const pendingPoll = new Promise<Integration[]>((resolve) => {
      resolvePoll = resolve;
    });
    vi.stubGlobal(
      'open',
      vi.fn(() => createPopup()),
    );
    api.getIntegrations
      .mockResolvedValueOnce([disconnected])
      .mockReturnValueOnce(pendingPoll);

    render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button'));
    await act(async () => {
      await Promise.resolve();
      await vi.advanceTimersByTimeAsync(3000);
    });

    expect(api.getIntegrations).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(9000);
    });
    expect(api.getIntegrations).toHaveBeenCalledTimes(2);

    await act(async () => {
      resolvePoll([connected]);
      await pendingPoll;
    });
    expect(screen.getByText('Connected')).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(api.getIntegrations).toHaveBeenCalledTimes(2);
  });

  it('stops polling at the timeout', async () => {
    vi.stubGlobal(
      'open',
      vi.fn(() => createPopup()),
    );

    render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(screen.getByText('Connection timed out. Please try again.')).toBeVisible();
    const callsAtTimeout = api.getIntegrations.mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(api.getIntegrations).toHaveBeenCalledTimes(callsAtTimeout);
  });

  it('stops polling when unmounted', async () => {
    vi.stubGlobal(
      'open',
      vi.fn(() => createPopup()),
    );

    const { unmount } = render(<ConnectedServices />);
    expect(await screen.findByText('Gmail')).toBeVisible();
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole('button'));
    await act(async () => {
      await Promise.resolve();
    });
    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(api.getIntegrations).toHaveBeenCalledTimes(1);
  });
});
