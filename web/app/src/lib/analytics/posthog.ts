import posthog from 'posthog-js';

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
  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },
  reset() {
    try {
      if (typeof window === 'undefined') return;
      this.init();
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
