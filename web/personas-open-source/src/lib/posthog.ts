import posthog from 'posthog-js';

const POSTHOG_KEY =
  process.env.NEXT_PUBLIC_POSTHOG_KEY ||
  'phc_xUxO7ovj7ckqMu2GhFltKeNM1EtVOSS6rnVhRH5ClIl';
const POSTHOG_HOST = process.env.NEXT_PUBLIC_POSTHOG_HOST || 'https://us.i.posthog.com';

let isInitialized = false;

type PostHogClient = {
  identify: (id: string, properties?: Record<string, unknown>) => void;
  capture: (event: string, properties?: Record<string, unknown>) => void;
  reset: () => void;
  setPersonProperties: (properties: Record<string, unknown>) => void;
};

const getClient = (): PostHogClient | null => {
  if (typeof window === 'undefined') return null;
  const snippet = (window as unknown as { posthog?: PostHogClient }).posthog;
  if (snippet && typeof snippet.capture === 'function') {
    return snippet;
  }
  return posthog;
};

export const PostHog = {
  init() {
    if (isInitialized || typeof window === 'undefined' || !POSTHOG_KEY) return;

    // Prefer the layout snippet if it already initialized PostHog.
    const snippet = (window as unknown as { posthog?: { capture?: unknown } }).posthog;
    if (snippet && typeof snippet.capture === 'function') {
      isInitialized = true;
      return;
    }

    posthog.init(POSTHOG_KEY, {
      api_host: POSTHOG_HOST,
      capture_pageview: false,
      persistence: 'localStorage',
      person_profiles: 'identified_only',
    });
    isInitialized = true;
  },

  identify(userId?: string, properties?: { name?: string; email?: string }) {
    if (typeof window === 'undefined') return;
    this.init();
    if (!userId) return;

    const client = getClient();
    if (!client) return;

    const person: Record<string, string> = { Platform: 'web' };
    if (properties?.name) person.name = properties.name;
    if (properties?.email) person.email = properties.email;
    client.identify(userId, person);
  },

  track(event: string, properties?: Record<string, unknown>) {
    if (typeof window === 'undefined') return;
    this.init();
    const client = getClient();
    if (!client) return;
    client.capture(event, properties);
  },

  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },

  reset() {
    if (typeof window === 'undefined') return;
    this.init();
    const client = getClient();
    if (!client) return;
    client.reset();
  },

  setUserProperty(key: string, value: unknown) {
    if (typeof window === 'undefined') return;
    this.init();
    const client = getClient();
    if (!client) return;
    client.setPersonProperties({ [key]: value });
  },
};
