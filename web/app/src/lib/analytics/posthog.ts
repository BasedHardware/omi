import posthog from 'posthog-js';

import { omiFlagEnabled, resetOmiFlags } from '@/lib/omiFlags';

const POSTHOG_KEY =
  process.env.NEXT_PUBLIC_POSTHOG_KEY ||
  'phc_xUxO7ovj7ckqMu2GhFltKeNM1EtVOSS6rnVhRH5ClIl';
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com';

let isInitialized = false;

export const PostHogManager = {
  init() {
    try {
      if (isInitialized || typeof window === 'undefined' || !POSTHOG_KEY) return;
      posthog.init(POSTHOG_KEY, {
        api_host: POSTHOG_HOST,
        autocapture: false,
        capture_pageview: false,
        persistence: 'localStorage',
        person_profiles: 'identified_only',
      });
      isInitialized = true;
    } catch {
      isInitialized = false;
    }
  },
  identify(userId: string, properties?: { name?: string; email?: string }) {
    try {
      if (typeof window === 'undefined') return;
      this.init();
      if (!isInitialized) return;
      const person: Record<string, string> = { Platform: 'web' };
      if (properties?.name) person.name = properties.name;
      if (properties?.email) person.email = properties.email;
      posthog.identify(userId, person);
    } catch {
      // Analytics must not block the caller.
    }
  },
  track(event: string, properties?: Record<string, unknown>) {
    try {
      if (typeof window === 'undefined') return;
      this.init();
      if (!isInitialized) return;
      posthog.capture(event, properties);
    } catch {
      // A throwing capture must not block checkout.
    }
  },
  /**
   * Resolve a boolean flag: Omi's flag store first for the keys it owns, else
   * once PostHog has delivered flags. Fails closed: no SDK, a throw, or no
   * answer within `timeoutMs` reads as off.
   */
  async isFeatureEnabled(flag: string, timeoutMs = 2000): Promise<boolean> {
    try {
      const omi = await omiFlagEnabled(flag, { timeoutMs });
      if (omi !== undefined) return omi;
    } catch {
      // Omi store unavailable: PostHog answers.
    }
    return this.isPostHogFeatureEnabled(flag, timeoutMs);
  },
  isPostHogFeatureEnabled(flag: string, timeoutMs: number): Promise<boolean> {
    try {
      if (typeof window === 'undefined') return Promise.resolve(false);
      this.init();
      if (!isInitialized) return Promise.resolve(false);
      return new Promise<boolean>((resolve) => {
        let unsubscribe: (() => void) | undefined;
        const finish = (enabled: boolean) => {
          clearTimeout(timer);
          unsubscribe?.();
          resolve(enabled);
        };
        const timer = setTimeout(() => finish(false), timeoutMs);
        try {
          unsubscribe = posthog.onFeatureFlags(() => {
            finish(posthog.isFeatureEnabled(flag) === true);
          });
        } catch {
          finish(false);
        }
      });
    } catch {
      return Promise.resolve(false);
    }
  },
  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },
  reset() {
    try {
      if (typeof window === 'undefined') return;
      this.init();
      resetOmiFlags();
      if (!isInitialized) return;
      posthog.reset();
    } catch {
      // Analytics must not block the caller.
    }
  },
  setUserProperty(key: string, value: unknown) {
    try {
      if (typeof window === 'undefined') return;
      this.init();
      if (!isInitialized) return;
      posthog.setPersonProperties({ [key]: value });
    } catch {
      // Analytics must not block the caller.
    }
  },
};
