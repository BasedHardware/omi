import mixpanel from 'mixpanel-browser';

// NOTE: mixpanel-browser is a browser-only SDK. App Router "use client"
// components are still server-rendered on the initial request, so this
// module is evaluated in Node during SSR. Calling mixpanel.init() at module
// scope crashes there (it touches localStorage/persistence that does not
// exist on the server) — under Next 15.5 this surfaces as
// "Cannot read properties of undefined (reading 'load_prop')".
// Initialize lazily on first client-side use and no-op on the server.
let initialized = false;

const ensureInit = () => {
  if (initialized || typeof window === 'undefined') return;
  mixpanel.init(process.env.NEXT_PUBLIC_MIXPANEL_TOKEN!, {
    debug: true,
    track_pageview: true,
    persistence: 'localStorage',
    api_host: 'https://api.mixpanel.com',
    ignore_dnt: true,
    loaded: () => {
      console.log('Mixpanel loaded successfully');
    },
  });
  initialized = true;
};

// Generate a unique anonymous ID if one doesn't exist
const getOrCreateAnonymousId = () => {
  let anonymousId = localStorage.getItem('mp_anonymous_id');
  if (!anonymousId) {
    anonymousId = 'anon-' + Math.random().toString(36).substr(2, 9);
    localStorage.setItem('mp_anonymous_id', anonymousId);
  }
  return anonymousId;
};

// Helper functions
export const Mixpanel = {
  identify: (id?: string) => {
    if (typeof window === 'undefined') return;
    ensureInit();
    const anonymousId = id || getOrCreateAnonymousId();
    mixpanel.identify(anonymousId);
    console.log('Identified user:', anonymousId);
  },

  track: (name: string, props?: any) => {
    if (typeof window === 'undefined') return;
    try {
      ensureInit();
      const anonymousId = getOrCreateAnonymousId();
      const eventProps = {
        distinct_id: anonymousId,
        ...props,
      };
      console.log('Tracking event:', name, eventProps);
      mixpanel.track(name, eventProps);
    } catch (e) {
      console.error('Mixpanel error:', e);
    }
  },
};
