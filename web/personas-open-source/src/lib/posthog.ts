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
  return null;
};

export const PostHog = {
  identify(userId?: string, properties?: { name?: string; email?: string }) {
    if (!userId) return;
    const client = getClient();
    if (!client) return;

    const person: Record<string, string> = { Platform: 'web' };
    if (properties?.name) person.name = properties.name;
    if (properties?.email) person.email = properties.email;
    client.identify(userId, person);
  },

  track(event: string, properties?: Record<string, unknown>) {
    const client = getClient();
    if (!client) return;
    client.capture(event, properties);
  },

  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },

  reset() {
    const client = getClient();
    if (!client) return;
    client.reset();
  },

  setUserProperty(key: string, value: unknown) {
    const client = getClient();
    if (!client) return;
    client.setPersonProperties({ [key]: value });
  },
};
