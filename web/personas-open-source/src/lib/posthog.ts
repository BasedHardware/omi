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

// The layout snippet loads `afterInteractive`, so component effects can call
// the wrapper before `window.posthog` exists. Buffer calls until the snippet
// is ready so early events (e.g. the initial `Page View`) are replayed in
// order instead of silently dropped. If the snippet never loads, stop
// polling and drop the buffer to match the previous no-op behavior.
type PendingCall = (client: PostHogClient) => void;

const pendingCalls: PendingCall[] = [];
let snippetPoll: ReturnType<typeof setInterval> | null = null;
const SNIPPET_POLL_INTERVAL_MS = 100;
const SNIPPET_POLL_TIMEOUT_MS = 10_000;

const flushPending = (client: PostHogClient) => {
  const calls = pendingCalls.splice(0);
  for (const call of calls) call(client);
};

const dispatch = (call: PendingCall) => {
  // SSR has no snippet to wait for: no-op, matching the previous behavior.
  if (typeof window === 'undefined') return;
  const client = getClient();
  if (client) {
    flushPending(client);
    call(client);
    return;
  }
  pendingCalls.push(call);
  if (snippetPoll !== null) return;
  const startedAt = Date.now();
  snippetPoll = setInterval(() => {
    const ready = getClient();
    if (ready) flushPending(ready);
    if (!ready && Date.now() - startedAt < SNIPPET_POLL_TIMEOUT_MS) return;
    if (snippetPoll !== null) {
      clearInterval(snippetPoll);
      snippetPoll = null;
    }
    if (!ready) pendingCalls.length = 0;
  }, SNIPPET_POLL_INTERVAL_MS);
};

export const PostHog = {
  identify(userId?: string, properties?: { name?: string; email?: string }) {
    if (!userId) return;
    const person: Record<string, string> = { Platform: 'web' };
    if (properties?.name) person.name = properties.name;
    if (properties?.email) person.email = properties.email;
    dispatch((client) => client.identify(userId, person));
  },

  track(event: string, properties?: Record<string, unknown>) {
    dispatch((client) => client.capture(event, properties));
  },

  pageView(pageName: string) {
    this.track(`${pageName} Page Viewed`);
  },

  reset() {
    dispatch((client) => client.reset());
  },

  setUserProperty(key: string, value: unknown) {
    dispatch((client) => client.setPersonProperties({ [key]: value }));
  },
};

