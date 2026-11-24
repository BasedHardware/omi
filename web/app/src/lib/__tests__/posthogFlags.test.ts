import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('posthog-js', () => ({
  default: {
    init: vi.fn(),
    identify: vi.fn(),
    capture: vi.fn(),
    reset: vi.fn(),
    setPersonProperties: vi.fn(),
    isFeatureEnabled: vi.fn(() => true),
    reloadFeatureFlags: vi.fn(),
  },
}));
vi.mock('@/lib/omiFlags', () => ({ omiFlagEnabled: vi.fn(), resetOmiFlags: vi.fn() }));
import posthog from 'posthog-js';
import { omiFlagEnabled } from '@/lib/omiFlags';
import { PostHogManager } from '@/lib/analytics/posthog';

describe('Omi-only flags with PostHog capture', () => {
  beforeEach(() => vi.clearAllMocks());

  it('disables SDK flag loading while capture and identify still reach the SDK', () => {
    PostHogManager.init();
    expect(posthog.init).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ advanced_disable_feature_flags: true }),
    );
    PostHogManager.identify('test-user');
    PostHogManager.track('Chat Message Sent');
    expect(posthog.identify).toHaveBeenCalledWith('test-user', { Platform: 'web' });
    expect(posthog.capture).toHaveBeenCalledWith('Chat Message Sent', undefined);
  });

  it('uses Omi; unknown, failed and throwing reads never consult PostHog', async () => {
    vi.mocked(omiFlagEnabled)
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('offline'));
    expect(await PostHogManager.isFeatureEnabled('on')).toBe(true);
    expect(await PostHogManager.isFeatureEnabled('off')).toBe(false);
    expect(await PostHogManager.isFeatureEnabled('missing')).toBe(false);
    expect(await PostHogManager.isFeatureEnabled('failed')).toBe(false);
    expect(posthog.isFeatureEnabled).not.toHaveBeenCalled();
    expect(posthog.reloadFeatureFlags).not.toHaveBeenCalled();
  });
});
