import posthog from 'posthog-js';

const POSTHOG_KEY =
  process.env.NEXT_PUBLIC_POSTHOG_KEY ||
  'phc_xUxO7ovj7ckqMu2GhFltKeNM1EtVOSS6rnVhRH5ClIl';
const POSTHOG_HOST =
  process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com';

let isInitialized = false;

export const PostHogManager = {
  init() {
    if (isInitialized || typeof window === 'undefined' || !POSTHOG_KEY) return;
    posthog.init(POSTHOG_KEY, {
      api_host: POSTHOG_HOST,
      autocapture: false,
      capture_pageview: false,
      persistence: 'localStorage',
      person_profiles: 'identified_only',
    });
    isInitialized = true;
  },
  identify(userId: string, properties?: { name?: string; email?: string }) {
    if (typeof window === 'undefined') return;
    this.init();
    if (!isInitialized) return;
    const person: Record<string, string> = { Platform: 'web' };
    if (properties?.name) person.name = properties.name;
    if (properties?.email) person.email = properties.email;
    posthog.identify(userId, person);
  },
  track(event: string, properties?: Record<string, unknown>) {
    if (typeof window === 'undefined') return;
    this.init();
    if (!isInitialized) return;
    posthog.capture(event, properties);
  },
  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },
  reset() {
    if (typeof window === 'undefined') return;
    this.init();
    if (!isInitialized) return;
    posthog.reset();
  },
  setUserProperty(key: string, value: unknown) {
    if (typeof window === 'undefined') return;
    this.init();
    if (!isInitialized) return;
    posthog.setPersonProperties({ [key]: value });
  },
};
