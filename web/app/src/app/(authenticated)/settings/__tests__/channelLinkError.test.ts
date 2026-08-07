import { describe, expect, it, vi } from 'vitest';

vi.mock('@tschk/moonshine-next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/components/settings/SettingsPage', () => ({ SettingsPage: () => null }));
vi.mock('@/lib/analytics/mixpanel', () => ({ MixpanelManager: { pageView: vi.fn() } }));
vi.mock('@/components/auth/AuthProvider', () => ({ useAuth: () => ({ user: null }) }));
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/lib/api', () => ({ claimChannelLink: vi.fn() }));
vi.mock('@/moonshine/register-client-route', () => ({
  registerMoonshineRoute: vi.fn(),
}));

const { describeChannelLinkError } = await import('@/app/(authenticated)/settings/page');

// Every one of these used to read "This link is invalid or expired", which is
// only true for the rejected-code case and hides what the reader should do.
describe('describeChannelLinkError', () => {
  it('keeps the invalid-or-expired wording for a rejected code', () => {
    expect(describeChannelLinkError(new Error('API error: 400 Bad Request'))).toBe(
      'This link is invalid or expired',
    );
  });

  it('says the channel is already linked on a conflict', () => {
    const message = describeChannelLinkError(new Error('API error: 409 Conflict'));
    expect(message).toMatch(/already linked/i);
    expect(message).not.toMatch(/invalid or expired/i);
  });

  it('asks for a fresh sign-in when the session expired', () => {
    for (const error of [
      new Error('Unauthorized - please sign in again'),
      new Error('Not authenticated'),
    ]) {
      const message = describeChannelLinkError(error);
      expect(message).toMatch(/sign in/i);
      expect(message).not.toMatch(/invalid or expired/i);
    }
  });

  it('names the connection when the request never reached the API', () => {
    const message = describeChannelLinkError(
      new Error('Network error: Unable to reach the API. Please check your connection.'),
    );
    expect(message).toMatch(/connection/i);
    expect(message).not.toMatch(/invalid or expired/i);
  });

  it('does not claim the link is bad for an unrecognised server failure', () => {
    const message = describeChannelLinkError(
      new Error('API error: 500 Internal Server Error'),
    );
    expect(message).not.toMatch(/invalid or expired/i);
  });
});
